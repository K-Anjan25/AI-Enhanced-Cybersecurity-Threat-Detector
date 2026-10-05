"""Tests for the evaluation harness (T-112).

The metric values here are hand-computed or taken from the textbook example
(scores ``[0.1, 0.4, 0.35, 0.8]``, labels ``[0, 0, 1, 1]``, ROC-AUC 0.75,
average precision 0.8333) rather than captured from a previous run, so a
regression shows up as a wrong number rather than as a changed expectation.
"""

from __future__ import annotations

import json

import pytest
from aegis_ml.data.features import extract_flow_window
from aegis_ml.data.synthetic import GenerationSpec, Scenario, generate_flows
from aegis_ml.data.windowing import window_flows
from aegis_ml.training.evaluation import (
    DEFAULT_SWEEP_STEPS,
    EVAL_SCHEMA_VERSION,
    EvalReport,
    average_precision,
    confusion_at,
    evaluate,
    roc_auc,
    threshold_sweep,
)
from pydantic import ValidationError

#: The textbook example.
SCORES = [0.1, 0.4, 0.35, 0.8]
LABELS = [False, False, True, True]


def test_confusion_matrix_is_hand_computable() -> None:
    """At 0.5 only 0.8 is predicted positive: one true positive, one miss."""
    counts = confusion_at(SCORES, LABELS, 0.5)

    assert (counts.tp, counts.fp, counts.tn, counts.fn) == (1, 0, 2, 1)


def test_a_score_equal_to_the_threshold_counts_as_positive() -> None:
    """The boundary rule is what makes the sweep monotone."""
    assert confusion_at([0.5, 0.4], [True, False], 0.5).tp == 1
    assert confusion_at([0.5, 0.4], [True, False], 0.51).fn == 1


def test_roc_auc_matches_the_textbook_value() -> None:
    assert roc_auc(SCORES, LABELS) == pytest.approx(0.75)


def test_average_precision_matches_the_textbook_value() -> None:
    assert average_precision(SCORES, LABELS) == pytest.approx(5 / 6)


def test_tied_scores_do_not_depend_on_their_order() -> None:
    """Equal scores share an average rank, so reordering cannot move the metric."""
    scores = [0.5, 0.5, 0.2, 0.9]
    labels = [True, False, False, True]
    reordered = [0.2, 0.9, 0.5, 0.5]
    relabelled = [False, True, False, True]

    assert roc_auc(scores, labels) == pytest.approx(0.875)
    assert roc_auc(reordered, relabelled) == pytest.approx(roc_auc(scores, labels))
    assert average_precision(reordered, relabelled) == pytest.approx(
        average_precision(scores, labels)
    )


def test_perfect_and_inverted_separators() -> None:
    clean = ([0.1, 0.2, 0.8, 0.9], [False, False, True, True])
    inverted = ([0.9, 0.8, 0.2, 0.1], [False, False, True, True])

    assert roc_auc(*clean) == 1.0
    assert average_precision(*clean) == 1.0
    assert roc_auc(*inverted) == 0.0


def test_undefined_metrics_raise_instead_of_returning_nan() -> None:
    """A NaN in a metrics table gets read as zero by the next person."""
    with pytest.raises(ValueError, match="needs both classes"):
        roc_auc([0.1, 0.2], [False, False])

    with pytest.raises(ValueError, match="needs both classes"):
        roc_auc([0.1, 0.2], [True, True])

    with pytest.raises(ValueError, match="at least one positive"):
        average_precision([0.1, 0.2], [False, False])


def test_the_sweep_covers_the_whole_range_and_is_monotone() -> None:
    sweep = threshold_sweep(SCORES, LABELS)

    assert len(sweep) == DEFAULT_SWEEP_STEPS
    assert sweep[0].threshold == 0.0
    assert sweep[-1].threshold == 1.0
    recalls = [point.recall for point in sweep]
    fprs = [point.fpr for point in sweep]
    assert recalls == sorted(recalls, reverse=True), "recall cannot rise with the threshold"
    assert fprs == sorted(fprs, reverse=True)


def test_best_f1_is_the_maximum_over_the_sweep() -> None:
    report = evaluate(SCORES, LABELS, model_id="m1")

    assert report.best_f1.threshold == pytest.approx(0.35)
    assert report.best_f1.f1 == pytest.approx(0.8)
    assert report.best_f1.f1 == max(point.f1 for point in report.sweep)


def test_best_f1_ties_break_toward_the_higher_threshold() -> None:
    """Equal F1 means fewer false positives, which is the safer operating point."""
    scores = [0.2, 0.4, 0.6, 0.8]
    labels = [False, True, False, True]
    sweep = threshold_sweep(scores, labels)
    tied = [point for point in sweep if point.f1 == max(p.f1 for p in sweep)]

    assert len(tied) > 1, "the fixture must actually produce a tie"
    report = evaluate(scores, labels, model_id="m1")
    assert report.best_f1.threshold == max(point.threshold for point in tied)


def test_the_report_is_a_validated_schema() -> None:
    report = evaluate(SCORES, LABELS, model_id="m1")

    assert report.schema_version == EVAL_SCHEMA_VERSION == "eval@1"
    assert report.positives == 2 and report.negatives == 2
    assert report.metrics.accuracy == pytest.approx(0.75)

    payload = json.loads(report.model_dump_json())
    with pytest.raises(ValidationError):
        EvalReport.model_validate({**payload, "surprise": 1})


def test_the_schema_rejects_impossible_values() -> None:
    report = evaluate(SCORES, LABELS, model_id="m1")
    payload = json.loads(report.model_dump_json())

    with pytest.raises(ValidationError):
        EvalReport.model_validate({**payload, "schema_version": "eval@2"})
    with pytest.raises(ValidationError):
        EvalReport.model_validate({**payload, "metrics": {**payload["metrics"], "roc_auc": 1.4}})
    with pytest.raises(ValidationError):
        EvalReport.model_validate({**payload, "model_id": ""})
    with pytest.raises(ValidationError):
        EvalReport.model_validate({**payload, "confusion": {**payload["confusion"], "tp": -1}})


def test_running_twice_yields_identical_bytes() -> None:
    """The acceptance criterion: the same artifact, the same numbers, byte for byte."""
    first = evaluate(SCORES, LABELS, model_id="m1").model_dump_json()
    second = evaluate(SCORES, LABELS, model_id="m1").model_dump_json()

    assert first == second
    assert len(first) > 500, "the sweep should make this a substantial document"


def test_reordering_the_input_does_not_change_the_metrics() -> None:
    """Only the confusion-free, order-independent measures are asserted here."""
    scores = [0.1, 0.4, 0.35, 0.8, 0.55]
    labels = [False, False, True, True, True]
    shuffled = [0.55, 0.1, 0.8, 0.4, 0.35]
    shuffled_labels = [True, False, True, False, True]

    a = evaluate(scores, labels, model_id="m")
    b = evaluate(shuffled, shuffled_labels, model_id="m")

    assert a.metrics == b.metrics
    assert a.confusion == b.confusion


def test_inputs_are_validated() -> None:
    with pytest.raises(ValueError, match="empty set of scores"):
        evaluate([], [], model_id="m")

    with pytest.raises(ValueError, match="2 scores but 3 labels"):
        evaluate([0.1, 0.2], [True, False, True], model_id="m")

    with pytest.raises(ValueError, match="at least 2 steps"):
        threshold_sweep(SCORES, LABELS, steps=1)


# --- end to end over the synthetic pipeline ------------------------------


def scored_windows() -> tuple[list[float], list[bool]]:
    """Score windows by how many distinct destination ports they touch.

    A deliberately trivial scorer: it exists to exercise the path from generated
    telemetry through windowing and feature extraction into the harness, not to
    be a good detector.
    """
    scores: list[float] = []
    labels: list[bool] = []
    for scenario in (Scenario.PORT_SCAN, Scenario.NORMAL):
        flows = generate_flows(GenerationSpec(scenario, 200, 7))
        for window in window_flows(flows, size=50):
            rows = extract_flow_window(window.records)
            scores.append(min(1.0, rows[0].numeric_value("dst_port_count") / 50.0))
            labels.append(rows[0].label != "normal")
    return scores, labels


def test_the_harness_runs_over_the_whole_synthetic_pipeline() -> None:
    scores, labels = scored_windows()

    report = evaluate(scores, labels, model_id="port-count-probe")

    assert report.positives > 0 and report.negatives > 0
    assert report.metrics.roc_auc > 0.9, "port count alone should separate a scan"
    assert report.best_f1.f1 > 0.9
    assert report.model_id == "port-count-probe"


def test_a_useless_scorer_scores_like_a_coin_flip() -> None:
    """Guards against a harness that flatters every input."""
    scores, labels = scored_windows()
    constant = [0.5 for _ in scores]

    report = evaluate(constant, labels, model_id="constant", threshold=0.5)

    assert report.metrics.roc_auc == 0.5
    assert report.precision == pytest.approx(sum(labels) / len(labels))
