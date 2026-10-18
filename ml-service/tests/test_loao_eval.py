"""Window-level leave-one-attacker-out evaluation: threshold, scores and report."""

from __future__ import annotations

import pytest
from aegis_ml.training.loao_eval import (
    DEFAULT_MAX_BENIGN_FPR,
    loao_report,
    operating_point,
    threshold_for_fpr,
    window_scores,
)


def test_threshold_keeps_benign_false_positives_within_the_limit() -> None:
    benign = [i / 1000 for i in range(1000)]  # 1000 distinct benign scores

    threshold = threshold_for_fpr(benign, max_fpr=0.005)
    flagged = sum(1 for s in benign if s >= threshold)

    assert flagged <= int(0.005 * len(benign))


def test_threshold_is_the_smallest_that_meets_the_limit() -> None:
    """One more benign window flagged would break the limit."""
    benign = [i / 1000 for i in range(1000)]
    threshold = threshold_for_fpr(benign, max_fpr=0.005)

    assert sum(1 for s in benign if s >= threshold) == 5
    assert sum(1 for s in benign if s >= threshold - 0.001) == 6


def test_threshold_is_safe_with_tied_scores() -> None:
    """Ties at the cut must not be flagged past the limit."""
    benign = [0.5] * 100 + [0.1] * 100

    threshold = threshold_for_fpr(benign, max_fpr=0.01)

    assert sum(1 for s in benign if s >= threshold) <= 2


def test_threshold_validates_its_input() -> None:
    with pytest.raises(ValueError, match="without benign validation scores"):
        threshold_for_fpr([], max_fpr=0.005)
    with pytest.raises(ValueError, match="max_fpr must be in"):
        threshold_for_fpr([0.1, 0.2], max_fpr=0.0)
    with pytest.raises(ValueError, match="max_fpr must be in"):
        threshold_for_fpr([0.1, 0.2], max_fpr=1.0)


def test_default_limit_is_the_prd_benign_false_positive_rate() -> None:
    assert DEFAULT_MAX_BENIGN_FPR == 0.005


def test_window_score_is_the_highest_row_score() -> None:
    """One flagged flow flags its window, whatever the other flows say."""
    assert window_scores([[0.1, 0.9, 0.2], [0.05], [0.3, 0.3]]) == [0.9, 0.05, 0.3]


def test_a_window_with_no_rows_is_refused() -> None:
    with pytest.raises(ValueError, match="window 1 has no rows"):
        window_scores([[0.1], []])


def test_operating_point_counts_and_rates() -> None:
    scores = [0.9, 0.8, 0.4, 0.2]
    labels = [True, False, True, False]

    point = operating_point(scores, labels, threshold=0.5)

    assert (point.tp, point.fp, point.fn, point.tn) == (1, 1, 1, 1)
    assert point.precision == 0.5
    assert point.recall == 0.5
    assert point.fpr == 0.5


def test_operating_point_length_mismatch_is_refused() -> None:
    with pytest.raises(ValueError, match="same length"):
        operating_point([0.1], [True, False], threshold=0.5)


def test_validation_attacks_never_move_the_threshold() -> None:
    """Only benign validation windows set the threshold."""
    benign = [0.1] * 200
    valid_scores = benign + [0.99, 0.98]
    valid_labels = [False] * 200 + [True, True]

    report = loao_report(
        test_scores=[0.5, 0.2],
        test_labels=[True, False],
        valid_scores=valid_scores,
        valid_labels=valid_labels,
    )

    assert report["valid_benign_windows"] == 200
    assert report["threshold"] < 0.99


def test_loao_report_scores_test_at_the_validation_threshold() -> None:
    valid_scores = [i / 100 for i in range(100)]
    valid_labels = [False] * 100
    # 5% of 100 benign windows may be flagged, so the threshold sits just above
    # the 6th-highest benign score (0.94). 0.97 and 0.96 clear it; 0.10 and 0.05 do not.
    test_scores = [0.97, 0.96, 0.10, 0.05]
    test_labels = [True, True, False, False]

    report = loao_report(test_scores, test_labels, valid_scores, valid_labels, max_fpr=0.05)

    assert report["test_positive_windows"] == 2
    assert report["test_negative_windows"] == 2
    assert report["roc_auc"] == 1.0
    assert report["recall"] == 1.0
    assert report["fpr"] == 0.0
    assert report["max_benign_fpr"] == 0.05


def test_loao_report_refuses_a_test_fold_with_one_class() -> None:
    with pytest.raises(ValueError, match="needs both classes"):
        loao_report([0.5, 0.6], [True, True], [0.1], [False], max_fpr=0.005)


def test_loao_report_refuses_no_benign_validation_windows() -> None:
    with pytest.raises(ValueError, match="without benign validation scores"):
        loao_report([0.5, 0.1], [True, False], [0.9], [True], max_fpr=0.005)


def test_loao_report_reports_precision_and_recall_at_the_high_band() -> None:
    # PRD FR-13: `high` starts at 0.75. The block is fixed, not validation-derived.
    valid_scores = [0.1, 0.2, 0.3]
    valid_labels = [False, False, False]
    test_scores = [0.9, 0.8, 0.7, 0.2]
    test_labels = [True, True, True, False]

    report = loao_report(test_scores, test_labels, valid_scores, valid_labels)
    high = report["at_high"]

    assert isinstance(high, dict)
    assert high["threshold"] == 0.75
    assert high["tp"] == 2
    assert high["fn"] == 1
    assert high["fp"] == 0
    assert high["recall"] == 2 / 3
    assert high["precision"] == 1.0
