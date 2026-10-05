"""T-308: the correlator bands, deduplicates, groups and persists alerts.

The acceptance criterion is narrow -- a duplicate ``(entity, family)`` inside the
cool-down increments ``occurrence_count`` instead of creating a row -- and it is
tested by counting rows in the store, not by reading the return value, because an
implementation that returns the right action and writes a second row would pass
the weaker test.

The rest of the suite covers the ways this can be subtly wrong: a boundary
handled on the wrong side, a replay that double-counts, a grouped case that never
clears ``partial_evidence``, and an alert raised without an explanation (R-70).

The fusion rule used here is the real one from ``aegis_ml.scoring.fusion``: the
correlator takes it as an injected dependency, so exercising the real arithmetic
through the interface is what verifies the two agree.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from aegis_ml.scoring.fusion import fuse
from app.db.models import Alert, AlertStatus
from app.services.correlator import (
    Action,
    AlertCase,
    Correlator,
    CorrelatorConfig,
    Detection,
    Explanation,
    InMemoryCaseStore,
    Modality,
    Severity,
    SeverityBands,
    alert_row,
    severity_for,
)

NOW = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)


def detection(
    *,
    entity_id: int = 7,
    family: str = "Reconnaissance",
    modality: Modality = Modality.flow,
    score: float = 0.8,
    at: datetime = NOW,
    evidence: str = "flow:10.0.0.7@100",
    model_id: str | None = "flownet@1.0.0",
    explanation: Explanation | None = None,
) -> Detection:
    """A valid detection, with every field overridable one at a time."""
    return Detection(
        entity_id=entity_id,
        family=family,
        modality=modality,
        score=score,
        at=at,
        evidence_id=evidence,
        model_id=model_id,
        explanation=explanation,
    )


def build(config: CorrelatorConfig | None = None) -> tuple[Correlator, InMemoryCaseStore]:
    """A correlator over an in-memory store, using the real fusion rule."""
    store = InMemoryCaseStore()
    return Correlator(store, fuse, config=config), store


# --- severity banding (FR-13) ----------------------------------------------


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (1.0, Severity.critical),
        (0.90, Severity.critical),
        (0.8999, Severity.high),
        (0.75, Severity.high),
        (0.5499, Severity.low),
        (0.55, Severity.medium),
        (0.35, Severity.low),
    ],
)
def test_a_score_on_a_band_boundary_lands_in_the_band_the_boundary_names(
    score: float, expected: Severity
) -> None:
    assert severity_for(score) is expected


@pytest.mark.parametrize("score", [0.0, 0.1, 0.3499])
def test_a_score_below_the_lowest_bound_is_info(score: float) -> None:
    assert severity_for(score) is Severity.info


@pytest.mark.parametrize("score", [-0.01, 1.01, 7.0])
def test_a_score_outside_the_unit_interval_is_refused_not_clamped(score: float) -> None:
    with pytest.raises(ValueError, match="score must be in"):
        severity_for(score)


def test_custom_bands_are_applied() -> None:
    strict = SeverityBands(critical=0.99, high=0.9, medium=0.7, low=0.5)
    assert severity_for(0.8, strict) is Severity.medium
    assert severity_for(0.8) is Severity.high


def test_bands_that_are_not_strictly_descending_are_refused() -> None:
    with pytest.raises(ValueError, match="strictly descending"):
        SeverityBands(critical=0.75, high=0.90, medium=0.55, low=0.35)


@pytest.mark.parametrize("value", [0.0, 1.0, -0.1])
def test_band_bounds_outside_the_open_unit_interval_are_refused(value: float) -> None:
    with pytest.raises(ValueError, match="must be in"):
        SeverityBands(critical=value)


# --- detection validation ---------------------------------------------------


def test_a_naive_timestamp_is_refused() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        detection(at=datetime(2026, 3, 15, 12, 0))  # noqa: DTZ001 - the point of the test


def test_a_detection_without_an_evidence_identity_is_refused() -> None:
    with pytest.raises(ValueError, match="identity of the window"):
        detection(evidence="  ")


def test_a_detection_without_a_family_is_refused() -> None:
    with pytest.raises(ValueError, match="threat family"):
        detection(family="")


def test_a_detection_score_outside_the_unit_interval_is_refused() -> None:
    with pytest.raises(ValueError, match="score must be in"):
        detection(score=1.2)


# --- creating a case --------------------------------------------------------


def test_the_first_detection_creates_an_open_case() -> None:
    correlator, store = build()
    outcome = correlator.ingest(detection())

    assert outcome.action is Action.created
    assert outcome.case.status is AlertStatus.open
    assert outcome.case.occurrence_count == 1
    assert len(store) == 1
    assert outcome.case.first_seen == outcome.case.last_seen == NOW


def test_a_single_modality_case_carries_the_fusion_penalty_and_the_flag() -> None:
    correlator, _ = build()
    outcome = correlator.ingest(detection(score=0.8))

    # The real rule removes 25% for one modality: 0.8 -> 0.6.
    assert outcome.case.score == pytest.approx(0.6)
    assert outcome.case.severity is Severity.medium
    assert outcome.case.partial_evidence is True


def test_a_case_id_is_derived_from_the_data() -> None:
    correlator, _ = build()
    outcome = correlator.ingest(detection(entity_id=7, evidence="flow:10.0.0.7@100"))
    assert outcome.case.id == "7:Reconnaissance:flow:10.0.0.7@100"


def test_a_different_entity_gets_its_own_case() -> None:
    correlator, store = build()
    correlator.ingest(detection(entity_id=7, evidence="flow:a@1"))
    correlator.ingest(detection(entity_id=8, evidence="flow:b@1"))
    assert len(store) == 2


def test_a_different_family_gets_its_own_case() -> None:
    correlator, store = build()
    correlator.ingest(detection(family="Reconnaissance", evidence="flow:a@1"))
    correlator.ingest(detection(family="Exfiltration", evidence="flow:a@2", score=0.9))
    assert len(store) == 2


# --- the cool-down (FR-15) and the acceptance criterion ---------------------


def test_a_repeat_inside_the_cool_down_increments_the_count_instead_of_inserting() -> None:
    correlator, store = build()
    correlator.ingest(detection())
    outcome = correlator.ingest(detection(at=NOW + timedelta(minutes=14), evidence="flow:7@200"))

    assert outcome.action is Action.absorbed
    assert outcome.case.occurrence_count == 2
    assert len(store) == 1  # the criterion: a count, not a second row


def test_a_repeat_exactly_at_the_cool_down_limit_is_still_one_incident() -> None:
    correlator, store = build()
    correlator.ingest(detection())
    outcome = correlator.ingest(detection(at=NOW + timedelta(minutes=15), evidence="flow:7@201"))

    assert outcome.action is Action.absorbed
    assert outcome.case.occurrence_count == 2
    assert len(store) == 1


def test_a_repeat_past_the_cool_down_opens_a_new_case() -> None:
    correlator, store = build()
    correlator.ingest(detection())
    outcome = correlator.ingest(
        detection(at=NOW + timedelta(minutes=15, seconds=1), evidence="flow:7@202")
    )

    assert outcome.action is Action.created
    assert len(store) == 2
    assert outcome.case.occurrence_count == 1


def test_a_repeat_moves_last_seen_and_keeps_first_seen() -> None:
    correlator, _ = build()
    correlator.ingest(detection())
    outcome = correlator.ingest(detection(at=NOW + timedelta(minutes=5), evidence="flow:7@203"))

    assert outcome.case.first_seen == NOW
    assert outcome.case.last_seen == NOW + timedelta(minutes=5)


def test_a_quieter_repeat_does_not_lower_the_case_score_or_severity() -> None:
    correlator, _ = build()
    first = correlator.ingest(detection(score=0.99, evidence="flow:7@1"))
    outcome = correlator.ingest(
        detection(score=0.4, at=NOW + timedelta(minutes=1), evidence="flow:7@2")
    )

    assert outcome.case.score == first.case.score
    assert outcome.case.severity is first.case.severity


def test_evicting_the_loudest_occurrence_does_not_lower_the_case_score() -> None:
    # Retention bounds what is displayed, not what was measured. With room for
    # one occurrence, the 0.99 that opened the case is evicted by a quieter
    # repeat -- and the case must still read at the severity it reached, or the
    # display retention has silently become an alert-severity input.
    correlator, _ = build(CorrelatorConfig(evidence_retention=1))
    first = correlator.ingest(detection(score=0.99, evidence="flow:7@1"))
    outcome = correlator.ingest(
        detection(score=0.4, at=NOW + timedelta(minutes=1), evidence="flow:7@2")
    )

    assert outcome.case.score == first.case.score
    assert outcome.case.severity is first.case.severity
    assert outcome.case.occurrences[-1].score == pytest.approx(0.4)


def test_escalation_is_visible_against_the_first_severity() -> None:
    correlator, _ = build()
    correlator.ingest(detection(score=0.6, evidence="flow:7@1"))
    outcome = correlator.ingest(
        detection(score=1.0, at=NOW + timedelta(minutes=1), evidence="flow:7@2")
    )

    assert outcome.case.first_severity is Severity.low
    assert outcome.case.severity is Severity.high
    assert outcome.case.score == pytest.approx(0.75)


def test_a_closed_case_does_not_absorb_a_repeat() -> None:
    correlator, store = build()
    created = correlator.ingest(detection())
    store.save(_with_status(created.case, AlertStatus.closed))

    outcome = correlator.ingest(detection(at=NOW + timedelta(minutes=1), evidence="flow:7@204"))
    assert outcome.action is Action.created
    assert len(store) == 2


def test_a_family_grouped_into_a_case_absorbs_its_own_repeats() -> None:
    correlator, store = build()
    correlator.ingest(detection(family="Reconnaissance", evidence="flow:7@1"))
    correlator.ingest(
        detection(
            family="Brute Force",
            modality=Modality.log,
            at=NOW + timedelta(seconds=30),
            evidence="log:7@1",
        )
    )
    outcome = correlator.ingest(
        detection(
            family="Brute Force",
            modality=Modality.log,
            at=NOW + timedelta(minutes=2),
            evidence="log:7@2",
        )
    )

    assert outcome.action is Action.absorbed
    assert len(store) == 1


# --- flow/log grouping (FR-19) ----------------------------------------------


def test_a_flow_and_a_log_detection_within_a_minute_become_one_case() -> None:
    correlator, store = build()
    correlator.ingest(detection(score=0.8))
    outcome = correlator.ingest(
        detection(
            family="Brute Force",
            modality=Modality.log,
            score=0.9,
            at=NOW + timedelta(seconds=30),
            evidence="log:7@1",
            model_id="lognet@1.0.0",
        )
    )

    assert outcome.action is Action.grouped
    assert len(store) == 1
    assert outcome.case.grouped is True
    assert outcome.case.families == ("Reconnaissance", "Brute Force")


def test_grouping_clears_the_partial_evidence_flag_and_raises_the_score() -> None:
    correlator, _ = build()
    single = correlator.ingest(detection(score=0.8))
    grouped = correlator.ingest(
        detection(
            modality=Modality.log,
            score=0.9,
            at=NOW + timedelta(seconds=30),
            evidence="log:7@1",
        )
    )

    assert single.case.partial_evidence is True
    assert grouped.case.partial_evidence is False
    # 0.6*0.8 + 0.4*0.9 = 0.84, against 0.75*0.8 = 0.6 for the penalised single side.
    assert grouped.case.score == pytest.approx(0.84)
    assert grouped.case.severity is Severity.high


def test_grouping_works_when_the_log_detection_arrives_first() -> None:
    correlator, store = build()
    correlator.ingest(
        detection(modality=Modality.log, score=0.9, evidence="log:7@1", model_id="lognet@1.0.0")
    )
    outcome = correlator.ingest(
        detection(score=0.8, at=NOW + timedelta(seconds=45), evidence="flow:7@1")
    )

    assert outcome.action is Action.grouped
    assert len(store) == 1
    assert outcome.case.partial_evidence is False


def test_detections_more_than_a_minute_apart_are_not_grouped() -> None:
    correlator, store = build()
    correlator.ingest(detection(evidence="flow:7@1"))
    outcome = correlator.ingest(
        detection(
            family="Brute Force",
            modality=Modality.log,
            at=NOW + timedelta(seconds=61),
            evidence="log:7@1",
        )
    )

    assert outcome.action is Action.created
    assert len(store) == 2


def test_two_detections_of_the_same_modality_are_not_grouped() -> None:
    correlator, _ = build()
    correlator.ingest(detection(evidence="flow:7@1"))
    outcome = correlator.ingest(
        detection(at=NOW + timedelta(seconds=10), evidence="flow:7@2", score=0.7)
    )

    assert outcome.action is Action.absorbed
    assert outcome.case.grouped is False


def test_a_closed_case_is_not_grouped_into() -> None:
    correlator, store = build()
    created = correlator.ingest(detection(evidence="flow:7@1"))
    store.save(_with_status(created.case, AlertStatus.closed))

    outcome = correlator.ingest(
        detection(
            modality=Modality.log,
            at=NOW + timedelta(seconds=10),
            evidence="log:7@1",
        )
    )
    assert outcome.action is Action.created
    assert len(store) == 2


def test_the_case_keeps_the_family_it_opened_with_but_records_every_family() -> None:
    correlator, _ = build()
    correlator.ingest(detection(family="Reconnaissance", evidence="flow:7@1"))
    outcome = correlator.ingest(
        detection(
            family="Brute Force",
            modality=Modality.log,
            at=NOW + timedelta(seconds=20),
            evidence="log:7@1",
        )
    )

    assert outcome.case.family == "Reconnaissance"
    assert outcome.case.families == ("Reconnaissance", "Brute Force")


# --- replay safety (T-307 emits at-least-once) ------------------------------


def test_a_replayed_window_is_a_no_op() -> None:
    correlator, store = build()
    correlator.ingest(detection())
    outcome = correlator.ingest(detection())

    assert outcome.action is Action.duplicate
    assert outcome.case.occurrence_count == 1
    assert len(store) == 1


def test_a_replay_after_the_cool_down_still_does_not_double_count() -> None:
    correlator, store = build()
    correlator.ingest(detection())
    outcome = correlator.ingest(detection(at=NOW + timedelta(minutes=30)))

    assert outcome.action is Action.duplicate
    assert outcome.case.occurrence_count == 1
    assert len(store) == 1


def test_a_replay_of_a_grouped_second_modality_is_a_no_op() -> None:
    correlator, _ = build()
    correlator.ingest(detection(evidence="flow:7@1"))
    second = detection(modality=Modality.log, at=NOW + timedelta(seconds=10), evidence="log:7@1")
    correlator.ingest(second)
    outcome = correlator.ingest(second)

    assert outcome.action is Action.duplicate
    assert outcome.case.occurrence_count == 2


# --- explanations (FR-14, R-70) ---------------------------------------------


def test_an_alert_without_an_explanation_is_still_raised_and_marked_unavailable() -> None:
    correlator, _ = build()
    outcome = correlator.ingest(detection(explanation=None))
    payload = outcome.case.explanation_payload()

    assert payload["explanation_unavailable"] is True
    assert "reasons" not in payload
    assert "detail" in payload


def test_a_blank_explanation_is_treated_as_unavailable() -> None:
    correlator, _ = build()
    outcome = correlator.ingest(detection(explanation=Explanation(reasons=(), unavailable=False)))
    assert outcome.case.explanation_payload()["explanation_unavailable"] is True


def test_reasons_from_both_modalities_appear_in_the_payload() -> None:
    correlator, _ = build()
    correlator.ingest(
        detection(
            evidence="flow:7@1",
            explanation=Explanation(reasons=("dst_port_count raised the score",)),
        )
    )
    outcome = correlator.ingest(
        detection(
            modality=Modality.log,
            at=NOW + timedelta(seconds=10),
            evidence="log:7@1",
            explanation=Explanation(reasons=("template auth-failed repeated",)),
        )
    )
    payload = outcome.case.explanation_payload()

    assert payload["reasons"] == [
        "dst_port_count raised the score",
        "template auth-failed repeated",
    ]
    assert "explanation_unavailable" not in payload


def test_at_most_three_reasons_per_modality_are_kept() -> None:
    correlator, _ = build()
    outcome = correlator.ingest(detection(explanation=Explanation(reasons=("a", "b", "c", "d"))))
    assert outcome.case.explanation_payload()["reasons"] == ["a", "b", "c"]


def test_an_unavailable_modality_is_named_alongside_the_other_modalitys_reasons() -> None:
    correlator, _ = build()
    correlator.ingest(
        detection(explanation=Explanation(reasons=("flow reason",)), evidence="flow:7@1")
    )
    outcome = correlator.ingest(
        detection(
            modality=Modality.log,
            at=NOW + timedelta(seconds=10),
            evidence="log:7@1",
            explanation=Explanation.unavailable_explanation("log model timed out"),
        )
    )
    payload = outcome.case.explanation_payload()

    assert payload["reasons"] == ["flow reason"]
    assert payload["unavailable_modalities"] == ["log"]
    assert "explanation_unavailable" not in payload


# --- retention ---------------------------------------------------------------


def test_the_occurrence_count_is_exact_beyond_the_display_retention() -> None:
    correlator, _ = build(CorrelatorConfig(evidence_retention=2))
    correlator.ingest(detection(evidence="flow:7@0"))
    for index in range(1, 5):
        outcome = correlator.ingest(
            detection(at=NOW + timedelta(seconds=index), evidence=f"flow:7@{index}")
        )

    assert outcome.case.occurrence_count == 5
    assert len(outcome.case.occurrences) == 2


def test_only_the_most_recent_occurrences_are_retained() -> None:
    correlator, _ = build(CorrelatorConfig(evidence_retention=2))
    for index in range(3):
        outcome = correlator.ingest(
            detection(at=NOW + timedelta(seconds=index), evidence=f"flow:7@{index}")
        )

    assert outcome.case.evidence_ids() == ("flow:7@1", "flow:7@2")


def test_the_evidence_pointer_survives_eviction_from_retention() -> None:
    correlator, _ = build(CorrelatorConfig(evidence_retention=1))
    correlator.ingest(detection(evidence="flow:7@first"))
    outcome = correlator.ingest(detection(at=NOW + timedelta(seconds=1), evidence="flow:7@last"))

    assert outcome.case.first_evidence_id == "flow:7@first"
    assert outcome.case.evidence_ids() == ("flow:7@last",)


# --- the store ----------------------------------------------------------------


def test_saving_a_case_again_updates_it_rather_than_duplicating_it() -> None:
    correlator, store = build()
    first = correlator.ingest(detection())
    store.save(_with_status(first.case, AlertStatus.acknowledged))

    assert len(store) == 1
    assert store.cases()[0].status is AlertStatus.acknowledged


def test_the_evidence_index_survives_eviction() -> None:
    correlator, store = build(CorrelatorConfig(evidence_retention=1))
    correlator.ingest(detection(evidence="flow:7@1"))
    correlator.ingest(detection(at=NOW + timedelta(seconds=1), evidence="flow:7@2"))

    assert store.case_with_evidence(7, "flow:7@1") is not None


def test_a_lookup_with_no_matching_case_returns_none() -> None:
    _, store = build()
    assert store.latest_for_entity(7, not_before=NOW) is None
    assert store.latest_for(7, {"Reconnaissance"}, not_before=NOW) is None
    assert store.case_with_evidence(7, "flow:7@1") is None


def test_latest_for_matches_any_family_a_case_carries() -> None:
    correlator, store = build()
    correlator.ingest(detection(family="Reconnaissance", evidence="flow:7@1"))
    correlator.ingest(
        detection(
            family="Brute Force",
            modality=Modality.log,
            at=NOW + timedelta(seconds=10),
            evidence="log:7@1",
        )
    )

    assert store.latest_for(7, {"Brute Force"}, not_before=NOW) is not None
    assert store.latest_for(7, {"Exfiltration"}, not_before=NOW) is None


def test_latest_for_excludes_cases_last_seen_before_the_bound() -> None:
    correlator, store = build()
    correlator.ingest(detection())
    assert store.latest_for_entity(7, not_before=NOW + timedelta(seconds=1)) is None


# --- the alert row ------------------------------------------------------------


def test_the_alert_row_names_only_real_alert_columns() -> None:
    correlator, _ = build()
    row = alert_row(correlator.ingest(detection()).case)
    assert set(row) <= {column.name for column in Alert.__table__.columns}
    assert "id" not in row and "created_at" not in row


def test_the_alert_row_reports_the_exact_occurrence_count_and_severity() -> None:
    correlator, _ = build()
    correlator.ingest(detection(score=0.99, evidence="flow:7@1"))
    outcome = correlator.ingest(detection(score=0.5, at=NOW + timedelta(minutes=1)))
    row = alert_row(outcome.case)

    assert row["occurrence_count"] == 2
    assert row["severity"] == outcome.case.severity.value
    assert row["score"] == outcome.case.score


def test_the_alert_row_keeps_the_pointer_to_the_first_window() -> None:
    correlator, _ = build(CorrelatorConfig(evidence_retention=1))
    correlator.ingest(detection(evidence="flow:7@first"))
    outcome = correlator.ingest(detection(at=NOW + timedelta(seconds=1), evidence="flow:7@last"))

    window_ref = alert_row(outcome.case)["window_ref"]
    assert isinstance(window_ref, dict)
    assert window_ref["id"] == "flow:7@first"
    assert window_ref["evidence"] == [
        {
            "id": "flow:7@last",
            "modality": "flow",
            "score": 0.8,
            "at": (NOW + timedelta(seconds=1)).isoformat(),
            "model": "flownet@1.0.0",
        }
    ]


def test_the_alert_row_records_both_model_ids_once_grouped() -> None:
    correlator, _ = build()
    correlator.ingest(detection(model_id="flownet@1.0.0", evidence="flow:7@1"))
    outcome = correlator.ingest(
        detection(
            modality=Modality.log,
            at=NOW + timedelta(seconds=10),
            evidence="log:7@1",
            model_id="lognet@2.1.0",
        )
    )
    row = alert_row(outcome.case)

    assert row["model_flow_id"] == "flownet@1.0.0"
    assert row["model_log_id"] == "lognet@2.1.0"


def test_the_alert_row_carries_the_explanation_or_the_marker() -> None:
    correlator, _ = build()
    explained = correlator.ingest(detection(explanation=Explanation(reasons=("one",))))
    unexplained = correlator.ingest(detection(entity_id=9, evidence="flow:9@1", explanation=None))

    assert alert_row(explained.case)["explanation"]["reasons"] == ["one"]  # type: ignore[index]
    marker = alert_row(unexplained.case)["explanation"]
    assert marker["explanation_unavailable"] is True  # type: ignore[index]


# --- configuration ------------------------------------------------------------


@pytest.mark.parametrize("value", [timedelta(0), timedelta(seconds=-1)])
def test_a_non_positive_cool_down_is_refused(value: timedelta) -> None:
    with pytest.raises(ValueError, match="cool_down must be positive"):
        CorrelatorConfig(cool_down=value)


@pytest.mark.parametrize("value", [timedelta(0), timedelta(seconds=-1)])
def test_a_non_positive_group_window_is_refused(value: timedelta) -> None:
    with pytest.raises(ValueError, match="group_window must be positive"):
        CorrelatorConfig(group_window=value)


def test_a_retention_below_one_is_refused() -> None:
    with pytest.raises(ValueError, match="evidence_retention"):
        CorrelatorConfig(evidence_retention=0)


def test_a_custom_cool_down_is_honoured() -> None:
    correlator, store = build(CorrelatorConfig(cool_down=timedelta(minutes=1)))
    correlator.ingest(detection())
    outcome = correlator.ingest(detection(at=NOW + timedelta(minutes=2), evidence="flow:7@2"))

    assert outcome.action is Action.created
    assert len(store) == 2


def test_the_config_exposes_the_default_policy() -> None:
    correlator, _ = build()
    assert correlator.config.cool_down == timedelta(minutes=15)
    assert correlator.config.group_window == timedelta(seconds=60)


def _with_status(case: AlertCase, status: AlertStatus) -> AlertCase:
    """A copy of a case with a different status, for the closed-case tests."""
    from dataclasses import replace

    return replace(case, status=status)
