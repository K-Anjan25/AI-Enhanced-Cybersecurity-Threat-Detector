"""T-322: the recalibration job, its window, its evidence and its guardrail.

FR-18's acceptance criteria are four claims, and each is asserted here against the
real T-207 arithmetic -- ``MlCalibrator`` over ``aegis_ml.scoring.thresholds``, the
same code the deployment runs, never a stub that agrees with the test:

* a run moves no threshold by more than the guardrail (0.10), and a fit that wants
  to move further is clamped rather than refused, with the requested value kept;
* every change is reported, and a run that changes nothing writes nothing;
* only ``benign``/``false_positive`` labels are fitted on -- a ``true_positive`` is
  not benign evidence, and unlabelled traffic has no representation to fit;
* too little feedback leaves the threshold alone instead of fitting to noise.

The numbers themselves are asserted to be T-207's, not copies: the quantile is
``DEFAULT_QUANTILE``, the guardrail is ``DEFAULT_GUARDRAIL``, and the minimum sample
is the inverse of the target false-positive rate rather than a round number someone
liked.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from aegis_ml.scoring.thresholds import DEFAULT_GUARDRAIL, DEFAULT_QUANTILE
from app.db.models import Verdict
from app.schemas.query import AlertQuery
from app.services.alert_store import InMemoryAlertStore
from app.services.ml_calibration import MlCalibrator
from app.services.recalibration import (
    BAND_DEFAULTS,
    BENIGN_LABELS,
    DEFAULT_TENANT_ID,
    DEFAULT_WINDOW,
    MIN_FEEDBACK,
    RECALIBRATED_SOURCE,
    AlertVerdictFeedback,
    InMemoryThresholdStore,
    LabelledScore,
    OutcomeReason,
    RecalibrationService,
    ThresholdKey,
    ThresholdRecord,
    UnfittableBand,
)
from app.services.verdict_service import InMemoryVerdictLedger, record_verdict

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
TENANT = DEFAULT_TENANT_ID
FAMILY = "lateral-movement"


# --- stubs -------------------------------------------------------------------


#: One entry in a stub's sample: a score, or a score with its own verdict.
Entry = float | tuple[float, Verdict]


class Feedback:
    """A :class:`FeedbackSource` over a family -> entries mapping.

    Records what it was asked for, so a test can assert the window and the tenant
    the job used rather than only what came back. An entry may carry its own
    verdict, which is how a test builds a mixed sample with one stub.
    """

    def __init__(
        self,
        by_family: dict[str, list[Entry]],
        *,
        verdict: Verdict = Verdict.benign,
        tenant_id: str = TENANT,
    ) -> None:
        """Bind the sample and the tenant this stub answers for."""
        self.by_family = by_family
        self.verdict = verdict
        self.tenant_id = tenant_id
        self.calls: list[tuple[str, datetime, datetime]] = []

    def labelled_scores(
        self, *, tenant_id: str, since: datetime, until: datetime
    ) -> Sequence[LabelledScore]:
        """Return one labelled score per entry, for the tenant this stub serves."""
        self.calls.append((tenant_id, since, until))
        if tenant_id != self.tenant_id:
            return ()
        found = []
        index = 0
        for family, entries in self.by_family.items():
            for entry in entries:
                index += 1
                score, decision = entry if isinstance(entry, tuple) else (entry, self.verdict)
                found.append(
                    LabelledScore(
                        alert_id=index,
                        family=family,
                        score=score,
                        verdict=decision,
                        alerted_at=until - timedelta(hours=1),
                        labelled_at=until - timedelta(minutes=30),
                    )
                )
        return tuple(found)


def spread(low: float, high: float, count: int) -> list[float]:
    """``count`` scores evenly spread over ``[low, high]``."""
    if count == 1:
        return [high]
    step = (high - low) / (count - 1)
    return [low + step * index for index in range(count)]


def service(
    feedback: Feedback,
    *,
    store: InMemoryThresholdStore | None = None,
    tenant_id: str = TENANT,
    window: timedelta = DEFAULT_WINDOW,
    minimum_sample: int = MIN_FEEDBACK,
) -> RecalibrationService:
    """The job, wired to the real calibrator."""
    return RecalibrationService(
        store=store if store is not None else InMemoryThresholdStore(),
        feedback=feedback,
        calibrator=MlCalibrator(),
        tenant_id=tenant_id,
        window=window,
        minimum_sample=minimum_sample,
    )


def row(family: str = FAMILY, band: str = "high", value: float = 0.75, tenant: str = TENANT):
    """One stored threshold row."""
    return ThresholdRecord(
        key=ThresholdKey(tenant, family, band),
        value=value,
        source="operator",
        updated_at=NOW - timedelta(days=1),
    )


# --- the numbers are T-207's, not ours ---------------------------------------


def test_the_documented_defaults_are_the_prd_bands() -> None:
    """R-69's initial values are FR-13's, read from the code the correlator bands by."""
    assert dict(BAND_DEFAULTS) == {"critical": 0.90, "high": 0.75, "medium": 0.55, "low": 0.35}
    from app.services.correlator import SeverityBands

    bands = SeverityBands()
    assert BAND_DEFAULTS["high"] == bands.high
    assert BAND_DEFAULTS["critical"] == bands.critical


def test_info_has_no_bound_to_recalibrate() -> None:
    """FR-13 gives ``info`` no lower bound, so there is no number to move."""
    assert "info" not in BAND_DEFAULTS
    with pytest.raises(ValueError, match="no documented lower bound"):
        ThresholdKey(TENANT, FAMILY, "info")


def test_the_window_is_the_fourteen_days_architecture_specifies() -> None:
    assert timedelta(days=14) == DEFAULT_WINDOW
    report = service(Feedback({FAMILY: spread(0.0, 0.5, 120)})).recalibrate(band="high", at=NOW)
    assert report.since == NOW - timedelta(days=14)
    assert report.until == NOW


def test_the_quantile_and_the_guardrail_are_the_ml_calibrators() -> None:
    """The criteria's numbers live in T-207; restating them here would fork them."""
    assert MlCalibrator().quantile == DEFAULT_QUANTILE == 0.99
    assert DEFAULT_GUARDRAIL == 0.10


def test_the_minimum_sample_is_the_inverse_of_the_target_rate() -> None:
    """Below ``1/(1-q)`` the quantile *is* an order statistic -- see the docstring."""
    assert MIN_FEEDBACK == round(1 / (1 - DEFAULT_QUANTILE)) == 100


def test_only_benign_and_false_positive_labels_are_benign_evidence() -> None:
    assert frozenset({Verdict.benign, Verdict.false_positive}) == BENIGN_LABELS
    assert Verdict.true_positive not in BENIGN_LABELS


# --- the guardrail -----------------------------------------------------------


def test_a_fit_within_the_guardrail_is_applied_as_requested() -> None:
    report = service(Feedback({FAMILY: spread(0.70, 0.80, 200)})).recalibrate(band="high", at=NOW)
    (outcome,) = report.outcomes
    assert outcome.previous == 0.75
    assert outcome.requested == pytest.approx(0.7999, abs=1e-3)
    assert outcome.applied == pytest.approx(outcome.requested)
    assert outcome.changed is True
    assert outcome.clamped is False


def test_a_fit_beyond_the_guardrail_is_clamped_and_still_applied() -> None:
    """Clamped, not refused: a threshold that cannot move is not a calibrated one."""
    store = InMemoryThresholdStore()
    store.put(row(value=0.55))
    report = service(Feedback({FAMILY: [0.99] * 200}), store=store).recalibrate(band="high", at=NOW)
    (outcome,) = report.outcomes
    assert outcome.requested == pytest.approx(0.99)
    assert outcome.applied == pytest.approx(0.55 + DEFAULT_GUARDRAIL)
    assert outcome.clamped is True
    assert outcome.changed is True
    assert outcome.applied - outcome.previous <= DEFAULT_GUARDRAIL


def test_the_requested_value_is_reported_even_when_the_guardrail_applies() -> None:
    """The interesting audit entry is the requested-and-refused one (T-207)."""
    report = service(Feedback({FAMILY: [0.99] * 120})).recalibrate(band="high", at=NOW)
    (outcome,) = report.outcomes
    assert outcome.requested == pytest.approx(0.99)
    assert outcome.applied == pytest.approx(0.85)
    assert outcome.requested != outcome.applied


def test_no_single_run_may_move_a_threshold_by_more_than_the_guardrail() -> None:
    """Ten runs towards the same distant threshold: every step is within 0.10."""
    store = InMemoryThresholdStore()
    job = service(Feedback({FAMILY: [0.99] * 200}), store=store)
    previous = 0.35
    for _ in range(10):
        (outcome,) = job.recalibrate(band="high", at=NOW).outcomes
        assert abs(outcome.applied - outcome.previous) <= DEFAULT_GUARDRAIL
        assert outcome.applied >= previous
        previous = outcome.applied
    assert previous == pytest.approx(0.99, abs=1e-2), "ten clamped runs must still arrive"


# --- too little feedback -----------------------------------------------------


def test_too_little_feedback_leaves_the_threshold_alone() -> None:
    """A fit from noise is worse than no fit: the row keeps its value."""
    store = InMemoryThresholdStore()
    store.put(row(value=0.62))
    report = service(
        Feedback({FAMILY: spread(0.0, 0.4, MIN_FEEDBACK - 1)}), store=store
    ).recalibrate(band="high", at=NOW)
    (outcome,) = report.outcomes
    assert outcome.reason is OutcomeReason.insufficient_feedback
    assert outcome.requested is None
    assert outcome.applied == 0.62
    assert outcome.changed is False
    assert outcome.sample_size == MIN_FEEDBACK - 1
    assert store.get(ThresholdKey(TENANT, FAMILY, "high")).value == 0.62  # type: ignore[union-attr]


def test_the_minimum_sample_is_the_boundary() -> None:
    """One score either side of the floor: the rule is the sample size, not luck."""
    refusals = service(Feedback({FAMILY: spread(0.0, 0.4, MIN_FEEDBACK - 1)}))
    assert refusals.recalibrate(band="high", at=NOW).refused
    assert refusals.recalibrate(band="high", at=NOW).changed == ()

    store = InMemoryThresholdStore()
    fitted = service(Feedback({FAMILY: [0.99] * MIN_FEEDBACK}), store=store)
    assert fitted.recalibrate(band="high", at=NOW).changed


# --- the evidence ------------------------------------------------------------


def test_a_true_positive_label_is_not_benign_evidence() -> None:
    """Attacks are not evidence about the benign distribution."""
    report = service(Feedback({FAMILY: [0.99] * 200}, verdict=Verdict.true_positive)).recalibrate(
        band="high", at=NOW
    )
    (outcome,) = report.outcomes
    assert outcome.reason is OutcomeReason.insufficient_feedback
    assert outcome.sample_size == 0
    assert outcome.applied == 0.75
    assert outcome.previous_was_default is True


def test_true_positives_do_not_dilute_a_benign_sample() -> None:
    """60 benign + 60 false-positive labels fit on 120; 200 true positives add nothing."""
    feedback = Feedback(
        {
            FAMILY: [(0.80, Verdict.benign)] * 60
            + [(0.80, Verdict.false_positive)] * 60
            + [(0.99, Verdict.true_positive)] * 200
        }
    )
    report = service(feedback).recalibrate(band="high", at=NOW)
    (outcome,) = report.outcomes
    assert outcome.sample_size == 120
    assert outcome.applied == pytest.approx(0.80)


def test_a_stored_value_is_what_the_fit_moves_from() -> None:
    """The value in force is the row's, not the default behind it."""
    store = InMemoryThresholdStore()
    store.put(row(value=0.70))
    report = service(Feedback({FAMILY: spread(0.70, 0.80, 200)}), store=store).recalibrate(
        band="high", at=NOW
    )
    (outcome,) = report.outcomes
    assert outcome.previous == 0.70
    assert outcome.previous_was_default is False
    assert outcome.applied == pytest.approx(0.7999, abs=1e-3)
    assert store.get(outcome.key).value == pytest.approx(outcome.applied)  # type: ignore[union-attr]


def test_a_fit_that_agrees_with_the_value_in_force_writes_nothing() -> None:
    """A fit that lands on the current value is a no-change run, not a write.

    ``changed`` is what the route records, so a fit that moves nothing must not
    create a row (or an audit entry) that says a threshold moved.
    """
    store = InMemoryThresholdStore()
    report = service(Feedback({FAMILY: [0.75] * 200}), store=store).recalibrate(band="high", at=NOW)
    (outcome,) = report.outcomes
    assert outcome.requested == pytest.approx(0.75)
    assert outcome.applied == pytest.approx(0.75)
    assert outcome.clamped is False
    assert outcome.changed is False
    assert report.changed == ()
    assert store.rows() == (), "agreement with the default is not a row"


def test_a_family_with_no_row_starts_from_the_documented_default() -> None:
    report = service(Feedback({FAMILY: [0.99] * 120})).recalibrate(band="high", at=NOW)
    (outcome,) = report.outcomes
    assert outcome.previous == BAND_DEFAULTS["high"]
    assert outcome.previous_was_default is True
    assert outcome.applied == pytest.approx(0.85)


def test_a_row_with_no_feedback_is_reported_not_dropped() -> None:
    store = InMemoryThresholdStore()
    store.put(row(value=0.62))
    report = service(Feedback({}), store=store).recalibrate(band="high", at=NOW)
    (outcome,) = report.outcomes
    assert outcome.key.family == FAMILY
    assert outcome.reason is OutcomeReason.insufficient_feedback
    assert outcome.sample_size == 0
    assert outcome.previous == 0.62
    assert outcome.previous_was_default is False


def test_the_fit_is_per_family() -> None:
    """Two families, two samples: neither fit is applied to the other's row."""
    feedback = Feedback({"alpha": [0.99] * 120, "beta": spread(0.2, 0.3, 120)})
    report = service(feedback).recalibrate(band="high", at=NOW)
    outcomes = {outcome.key.family: outcome for outcome in report.outcomes}
    assert outcomes["alpha"].applied == pytest.approx(0.85)
    # Downwards too: the guardrail is symmetric, so a fit far below the current
    # value moves one step and no further.
    assert outcomes["beta"].requested == pytest.approx(0.30, abs=1e-2)
    assert outcomes["beta"].applied == pytest.approx(0.65)
    assert outcomes["beta"].clamped is True


def test_a_corrupt_sample_refuses_the_run_before_anything_is_written() -> None:
    """The two-phase run: a bad family leaves the good one's row unwritten too."""
    store = InMemoryThresholdStore()
    feedback = Feedback({"alpha": [0.99] * 120, "zeta": [1.5] * 120})
    with pytest.raises(ValueError, match="outside"):
        service(feedback, store=store).recalibrate(band="high", at=NOW)
    assert store.rows() == ()


# --- the store and the tenant ------------------------------------------------


def test_only_the_named_band_is_touched() -> None:
    """A run is one band: another band's rows are not fitted and not reported."""
    store = InMemoryThresholdStore()
    store.put(row(band="medium", value=0.55))
    store.put(row(family="quiet", band="medium", value=0.30))
    report = service(Feedback({FAMILY: [0.99] * 120}), store=store).recalibrate(band="high", at=NOW)
    assert report.band == "high"
    assert [outcome.key.family for outcome in report.outcomes] == [FAMILY]
    assert store.get(ThresholdKey(TENANT, FAMILY, "medium")).value == 0.55  # type: ignore[union-attr]
    assert store.get(ThresholdKey(TENANT, "quiet", "medium")).value == 0.30  # type: ignore[union-attr]


def test_another_tenants_rows_are_neither_read_nor_written() -> None:
    """The tenant is part of the key, so a run cannot move -- or report -- a neighbour's bar."""
    store = InMemoryThresholdStore()
    store.put(row(tenant="acme", family="their-family", value=0.40))
    report = service(Feedback({FAMILY: [0.99] * 120}), store=store).recalibrate(band="high", at=NOW)
    assert {outcome.key.tenant_id for outcome in report.outcomes} == {TENANT}
    assert [outcome.key.family for outcome in report.outcomes] == [FAMILY]
    assert store.get(ThresholdKey("acme", "their-family", "high")).value == 0.40  # type: ignore[union-attr]


def test_a_run_names_the_tenant_it_covers() -> None:
    feedback = Feedback({FAMILY: [0.5] * 120}, tenant_id="acme")
    report = service(feedback, tenant_id="acme").recalibrate(band="high", at=NOW)
    assert report.tenant_id == "acme"
    assert feedback.calls == [("acme", NOW - DEFAULT_WINDOW, NOW)]


def test_rows_are_this_tenants_and_sorted() -> None:
    store = InMemoryThresholdStore()
    store.put(row(family="zeta", band="low", value=0.3))
    store.put(row(family="alpha", band="high", value=0.9))
    store.put(row(tenant="acme", family="alpha", band="high", value=0.4))
    listed = service(Feedback({}), store=store).rows()
    assert [(entry.key.family, entry.key.band) for entry in listed] == [
        ("alpha", "high"),
        ("zeta", "low"),
    ]


def test_a_changed_row_records_where_its_value_came_from() -> None:
    """R-69's provenance column: a recalibrated row says so."""
    store = InMemoryThresholdStore()
    service(Feedback({FAMILY: [0.99] * 120}), store=store).recalibrate(band="high", at=NOW)
    stored = store.get(ThresholdKey(TENANT, FAMILY, "high"))
    assert stored is not None
    assert stored.source == RECALIBRATED_SOURCE
    assert stored.updated_at == NOW
    assert stored.value == pytest.approx(0.85)


def test_the_store_replaces_a_row_in_place() -> None:
    store = InMemoryThresholdStore()
    store.put(row(value=0.5))
    store.put(row(value=0.6))
    assert len(store) == 1
    assert store.rows()[0].value == 0.6


# --- the report --------------------------------------------------------------


def test_outcome_reasons_are_stable_wire_strings() -> None:
    assert OutcomeReason.fitted.value == "fitted"
    assert OutcomeReason.insufficient_feedback.value == "insufficient_feedback"


def test_the_report_counts_what_it_did() -> None:
    store = InMemoryThresholdStore()
    store.put(row(family="quiet", value=0.5))
    feedback = Feedback({"loud": [0.99] * 120})
    report = service(feedback, store=store).recalibrate(band="high", at=NOW)
    assert [outcome.key.family for outcome in report.outcomes] == ["loud", "quiet"]
    assert len(report.changed) == 1
    assert len(report.refused) == 1
    assert report.quantile == DEFAULT_QUANTILE
    assert report.minimum_sample == MIN_FEEDBACK


def test_the_service_refuses_a_band_it_cannot_meaningfully_recalibrate() -> None:
    with pytest.raises(UnfittableBand, match="critical, high, low, medium"):
        service(Feedback({})).recalibrate(band="info", at=NOW)


def test_a_naive_instant_is_refused() -> None:
    """A naive instant is a different moment than the one the rows were written with."""
    with pytest.raises(ValueError, match="timezone-aware"):
        service(Feedback({})).recalibrate(band="high", at=datetime(2026, 10, 5, 12, 0))


@pytest.mark.parametrize(
    ("window", "minimum", "tenant"),
    [
        (timedelta(0), MIN_FEEDBACK, TENANT),
        (timedelta(days=1), 0, TENANT),
        (timedelta(days=1), MIN_FEEDBACK, "  "),
    ],
)
def test_a_configuration_that_cannot_run_is_refused(
    window: timedelta, minimum: int, tenant: str
) -> None:
    with pytest.raises(ValueError):
        RecalibrationService(
            store=InMemoryThresholdStore(),
            feedback=Feedback({}),
            calibrator=MlCalibrator(),
            tenant_id=tenant,
            window=window,
            minimum_sample=minimum,
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"value": 1.5},
        {"value": -0.1},
        {"source": "  "},
        {"updated_at": datetime(2026, 10, 5, 12, 0)},
    ],
)
def test_a_threshold_row_refuses_what_is_not_a_threshold(kwargs: dict[str, object]) -> None:
    fields: dict[str, object] = {
        "key": ThresholdKey(TENANT, FAMILY, "high"),
        "value": 0.5,
        "source": "operator",
        "updated_at": NOW,
    }
    fields.update(kwargs)
    with pytest.raises(ValueError):
        ThresholdRecord(**fields)  # type: ignore[arg-type]


def test_a_threshold_key_needs_a_tenant_and_a_family() -> None:
    with pytest.raises(ValueError, match="tenant_id"):
        ThresholdKey(" ", FAMILY, "high")
    with pytest.raises(ValueError, match="family"):
        ThresholdKey(TENANT, "", "high")


# --- the feedback source: the ledger joined to the alert store ---------------


def alert(store: InMemoryAlertStore, *, family: str, score: float, at: datetime, case: str):
    """Write one alert row the way the pipeline's writer would."""
    return store.save(
        case,
        {
            "entity_id": 1,
            "family": family,
            "severity": "high",
            "score": Decimal(str(score)),
            "window_ref": {"store": "stream", "id": case},
            "explanation": {},
            "status": "open",
            "first_seen": at,
            "last_seen": at,
            "occurrence_count": 1,
        },
        created_at=at,
    )


def verdict(ledger: InMemoryVerdictLedger, alert_row: object, decision: Verdict, at: datetime):
    """Record one verdict on a stored alert."""
    return record_verdict(
        ledger,
        alert_id=alert_row.id,  # type: ignore[attr-defined]
        alert_created_at=alert_row.created_at,  # type: ignore[attr-defined]
        verdict=decision,
        actor="analyst@corp",
        at=at,
    )


def feedback_source(
    store: InMemoryAlertStore, ledger: InMemoryVerdictLedger, **kwargs: object
) -> AlertVerdictFeedback:
    return AlertVerdictFeedback(store, ledger, **kwargs)  # type: ignore[arg-type]


def test_an_unlabelled_alert_is_not_evidence() -> None:
    store, ledger = InMemoryAlertStore(), InMemoryVerdictLedger()
    alert(store, family=FAMILY, score=0.9, at=NOW - timedelta(days=1), case="a")
    assert (
        feedback_source(store, ledger).labelled_scores(
            tenant_id=TENANT, since=NOW - DEFAULT_WINDOW, until=NOW
        )
        == ()
    )


def test_a_labelled_alert_carries_its_score_verdict_and_times() -> None:
    store, ledger = InMemoryAlertStore(), InMemoryVerdictLedger()
    stored = alert(store, family=FAMILY, score=0.91, at=NOW - timedelta(days=2), case="a")
    verdict(ledger, stored, Verdict.benign, NOW - timedelta(days=1))
    (found,) = feedback_source(store, ledger).labelled_scores(
        tenant_id=TENANT, since=NOW - DEFAULT_WINDOW, until=NOW
    )
    assert found.alert_id == stored.id
    assert found.family == FAMILY
    assert found.score == pytest.approx(0.91)
    assert found.verdict is Verdict.benign
    assert found.alerted_at == stored.created_at
    assert found.labelled_at == NOW - timedelta(days=1)


def test_the_latest_verdict_is_the_label_in_force() -> None:
    """A superseded verdict is history, not a label (T-309)."""
    store, ledger = InMemoryAlertStore(), InMemoryVerdictLedger()
    stored = alert(store, family=FAMILY, score=0.91, at=NOW - timedelta(days=2), case="a")
    verdict(ledger, stored, Verdict.benign, NOW - timedelta(days=2))
    verdict(ledger, stored, Verdict.true_positive, NOW - timedelta(days=1))
    (found,) = feedback_source(store, ledger).labelled_scores(
        tenant_id=TENANT, since=NOW - DEFAULT_WINDOW, until=NOW
    )
    assert found.verdict is Verdict.true_positive


def test_a_verdict_recorded_after_the_run_is_not_visible() -> None:
    """A run is reproducible: it sees the labels that existed at its instant."""
    store, ledger = InMemoryAlertStore(), InMemoryVerdictLedger()
    stored = alert(store, family=FAMILY, score=0.91, at=NOW - timedelta(days=2), case="a")
    verdict(ledger, stored, Verdict.benign, NOW + timedelta(minutes=1))
    assert (
        feedback_source(store, ledger).labelled_scores(
            tenant_id=TENANT, since=NOW - DEFAULT_WINDOW, until=NOW
        )
        == ()
    )


def test_an_alert_outside_the_window_is_not_read() -> None:
    store, ledger = InMemoryAlertStore(), InMemoryVerdictLedger()
    old = alert(
        store, family=FAMILY, score=0.91, at=NOW - DEFAULT_WINDOW - timedelta(days=1), case="a"
    )
    verdict(ledger, old, Verdict.benign, NOW - timedelta(days=1))
    assert (
        feedback_source(store, ledger).labelled_scores(
            tenant_id=TENANT, since=NOW - DEFAULT_WINDOW, until=NOW
        )
        == ()
    )


def test_another_tenants_feedback_is_refused_rather_than_mixed() -> None:
    """``alerts`` has no tenant column, so the source refuses what it cannot attribute."""
    store, ledger = InMemoryAlertStore(), InMemoryVerdictLedger()
    stored = alert(store, family=FAMILY, score=0.91, at=NOW - timedelta(days=1), case="a")
    verdict(ledger, stored, Verdict.benign, NOW - timedelta(hours=1))
    source = feedback_source(store, ledger)
    assert source.tenant_id == TENANT
    assert source.labelled_scores(tenant_id="acme", since=NOW - DEFAULT_WINDOW, until=NOW) == ()


def test_the_source_reads_through_the_query_api_s_own_bounds() -> None:
    """R-34: the read is time-bounded and paged, not a scan of the store."""
    ledger = InMemoryVerdictLedger()
    seen: list[AlertQuery] = []

    class Recorder(InMemoryAlertStore):
        def fetch(self, query: AlertQuery) -> list:
            seen.append(query)
            return super().fetch(query)

    recording = Recorder()
    stored = alert(recording, family=FAMILY, score=0.91, at=NOW - timedelta(days=1), case="a")
    verdict(ledger, stored, Verdict.benign, NOW - timedelta(hours=1))
    feedback_source(recording, ledger).labelled_scores(
        tenant_id=TENANT, since=NOW - DEFAULT_WINDOW, until=NOW
    )
    assert seen
    assert all(query.start == NOW - DEFAULT_WINDOW and query.end == NOW for query in seen)
    assert all(query.order == "asc" for query in seen)


def test_the_source_pages_through_more_rows_than_one_page() -> None:
    """A page loop that is never exercised is a page loop that does not work."""
    store, ledger = InMemoryAlertStore(), InMemoryVerdictLedger()
    for index in range(5):
        stored = alert(
            store,
            family=FAMILY,
            score=0.5 + index / 100,
            at=NOW - timedelta(days=1) + timedelta(minutes=index),
            case=f"case-{index}",
        )
        verdict(ledger, stored, Verdict.benign, NOW - timedelta(hours=1))
    found = feedback_source(store, ledger, page_size=2).labelled_scores(
        tenant_id=TENANT, since=NOW - DEFAULT_WINDOW, until=NOW
    )
    assert [entry.alert_id for entry in found] == [1, 2, 3, 4, 5]


def test_a_cursor_that_never_advances_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """No honest store does this; the guard is what keeps a weekly job from hanging."""
    monkeypatch.setattr(AlertVerdictFeedback, "MAX_PAGES", 3)

    class Stuck(InMemoryAlertStore):
        """Always answers the first page, as a broken cursor would."""

        def fetch(self, query: AlertQuery) -> list:
            return list(super().fetch(query.model_copy(update={"cursor": None})))

    store, ledger = Stuck(), InMemoryVerdictLedger()
    for index in range(4):
        stored = alert(
            store, family=FAMILY, score=0.5, at=NOW - timedelta(days=1), case=f"c{index}"
        )
        verdict(ledger, stored, Verdict.benign, NOW - timedelta(hours=1))
    with pytest.raises(RuntimeError, match="cursor is not advancing"):
        feedback_source(store, ledger, page_size=2).labelled_scores(
            tenant_id=TENANT, since=NOW - DEFAULT_WINDOW, until=NOW
        )


def test_the_source_refuses_a_window_that_is_naive_or_inverted() -> None:
    source = feedback_source(InMemoryAlertStore(), InMemoryVerdictLedger())
    with pytest.raises(ValueError, match="timezone-aware"):
        source.labelled_scores(tenant_id=TENANT, since=datetime(2026, 10, 5, 12, 0), until=NOW)
    with pytest.raises(ValueError, match="must increase"):
        source.labelled_scores(tenant_id=TENANT, since=NOW, until=NOW - timedelta(days=1))


def test_a_page_size_outside_the_query_s_own_limit_is_refused() -> None:
    with pytest.raises(ValueError, match="page_size"):
        feedback_source(InMemoryAlertStore(), InMemoryVerdictLedger(), page_size=0)
    with pytest.raises(ValueError, match="page_size"):
        feedback_source(InMemoryAlertStore(), InMemoryVerdictLedger(), page_size=10_000)


def test_the_real_stores_produce_a_fit_end_to_end() -> None:
    """The whole job: alerts, verdicts, the real calibrator, a moved threshold."""
    store, ledger = InMemoryAlertStore(), InMemoryVerdictLedger()
    for index in range(120):
        stored = alert(
            store,
            family=FAMILY,
            score=0.99,
            at=NOW - timedelta(days=1) + timedelta(seconds=index),
            case=f"case-{index}",
        )
        verdict(ledger, stored, Verdict.false_positive, NOW - timedelta(hours=1))
    job = service(AlertVerdictFeedback(store, ledger))  # type: ignore[arg-type]
    (outcome,) = job.recalibrate(band="high", at=NOW).outcomes
    assert outcome.sample_size == 120
    assert outcome.applied == pytest.approx(0.85)
    assert outcome.clamped is True
