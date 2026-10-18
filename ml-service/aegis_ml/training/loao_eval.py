"""Window-level evaluation for leave-one-attacker-out runs.

Both models are scored on the same windows, with the same labels:

* a window is an attack if it contains any attack flow (any-attack rule). The
  baselines previously scored only windows whose flows all carried one label,
  so they were tested on an easier subset than FlowNet;
* a baseline scores a window by its highest flow score, so one flagged flow
  flags its window, as it does for FlowNet, which scores windows directly.

The operating threshold is set on validation benign windows, not on the test
fold. It is the smallest threshold whose benign false-positive rate is at most
``max_fpr``. The PRD sets that limit at 0.5% (section 8). Threshold-free metrics
(ROC-AUC, PR-AUC) are reported alongside it.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from aegis_ml.training.evaluation import average_precision, roc_auc

#: PRD section 8: false-positive rate on benign traffic must not exceed 0.5%.
DEFAULT_MAX_BENIGN_FPR = 0.005
# PRD FR-13: the `high` severity band starts at score 0.75. PRD section 8 measures
# precision and recall at this deployed threshold, so it is reported beside the
# validation-set operating point rather than instead of it.
HIGH_BAND_THRESHOLD = 0.75


@dataclass(frozen=True)
class OperatingPoint:
    """Confusion counts and rates at one threshold, on one fold."""

    threshold: float
    tp: int
    fp: int
    tn: int
    fn: int

    @property
    def precision(self) -> float:
        """TP / (TP + FP); zero when nothing is flagged."""
        flagged = self.tp + self.fp
        return self.tp / flagged if flagged else 0.0

    @property
    def recall(self) -> float:
        """TP / (TP + FN); zero when the fold has no positives."""
        positives = self.tp + self.fn
        return self.tp / positives if positives else 0.0

    @property
    def fpr(self) -> float:
        """FP / (FP + TN); zero when the fold has no negatives."""
        negatives = self.fp + self.tn
        return self.fp / negatives if negatives else 0.0


def window_scores(per_window_row_scores: Sequence[Sequence[float]]) -> list[float]:
    """Score each window by its highest row score.

    Raises:
        ValueError: if a window has no rows, since it has no score to report.
    """
    scores: list[float] = []
    for index, row_scores in enumerate(per_window_row_scores):
        if not row_scores:
            raise ValueError(f"window {index} has no rows to score")
        scores.append(max(row_scores))
    return scores


def threshold_for_fpr(benign_scores: Sequence[float], max_fpr: float) -> float:
    """Return the smallest threshold that keeps benign false positives within ``max_fpr``.

    A window is flagged when its score is at least the threshold. The threshold
    returned is just above the benign score at the allowed rank, so at most
    ``floor(max_fpr * n)`` benign windows score at or above it, even with ties.

    Raises:
        ValueError: if there are no benign scores or ``max_fpr`` is not in (0, 1).
    """
    if not benign_scores:
        raise ValueError("cannot set a threshold without benign validation scores")
    if not 0.0 < max_fpr < 1.0:
        raise ValueError(f"max_fpr must be in (0, 1), got {max_fpr}")
    ordered = sorted(benign_scores, reverse=True)
    allowed = math.floor(max_fpr * len(ordered))
    return math.nextafter(ordered[allowed], math.inf)


def operating_point(
    scores: Sequence[float], labels: Sequence[bool], threshold: float
) -> OperatingPoint:
    """Confusion counts at ``threshold``: a window is flagged when score >= threshold."""
    if len(scores) != len(labels):
        raise ValueError("scores and labels must be the same length")
    tp = fp = tn = fn = 0
    for score, label in zip(scores, labels, strict=True):
        flagged = score >= threshold
        if label and flagged:
            tp += 1
        elif label:
            fn += 1
        elif flagged:
            fp += 1
        else:
            tn += 1
    return OperatingPoint(threshold=threshold, tp=tp, fp=fp, tn=tn, fn=fn)


def loao_report(
    test_scores: Sequence[float],
    test_labels: Sequence[bool],
    valid_scores: Sequence[float],
    valid_labels: Sequence[bool],
    *,
    max_fpr: float = DEFAULT_MAX_BENIGN_FPR,
) -> dict[str, object]:
    """Score one held-out attacker: threshold from validation, metrics on test.

    Only validation windows labelled benign set the threshold, so a validation
    attack can never move it.

    Raises:
        ValueError: if the test fold lacks either class, or there are no benign
            validation windows to set the threshold.
    """
    positives = sum(1 for label in test_labels if label)
    negatives = len(test_labels) - positives
    if positives == 0 or negatives == 0:
        raise ValueError(
            f"test fold needs both classes (positives={positives}, negatives={negatives})"
        )
    benign_valid = [s for s, label in zip(valid_scores, valid_labels, strict=True) if not label]
    threshold = threshold_for_fpr(benign_valid, max_fpr)
    point = operating_point(test_scores, test_labels, threshold)
    return {
        "test_windows": len(test_labels),
        "test_positive_windows": positives,
        "test_negative_windows": negatives,
        "valid_benign_windows": len(benign_valid),
        "max_benign_fpr": max_fpr,
        "threshold": threshold,
        "roc_auc": roc_auc(list(test_scores), list(test_labels)),
        "pr_auc": average_precision(list(test_scores), list(test_labels)),
        "precision": point.precision,
        "recall": point.recall,
        "fpr": point.fpr,
        "tp": point.tp,
        "fp": point.fp,
        "tn": point.tn,
        "fn": point.fn,
        "at_high": _at_high(test_scores, test_labels),
    }


def _at_high(scores: Sequence[float], labels: Sequence[bool]) -> dict[str, object]:
    """Precision and recall at the deployed `high` band (score >= 0.75)."""
    point = operating_point(scores, labels, HIGH_BAND_THRESHOLD)
    return {
        "threshold": HIGH_BAND_THRESHOLD,
        "precision": point.precision,
        "recall": point.recall,
        "fpr": point.fpr,
        "tp": point.tp,
        "fp": point.fp,
        "fn": point.fn,
        "tn": point.tn,
    }
