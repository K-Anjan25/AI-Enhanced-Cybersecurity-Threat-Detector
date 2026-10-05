"""Threshold calibration per family and tenant, under a movement guardrail (T-207).

A detector's threshold is the one number an operator actually feels: move it and
the alert volume moves with it. Two rules keep that from becoming a way to make a
bad week look quiet.

**A single run cannot move a threshold by more than the guardrail.** Calibration
is fitted from recent traffic, so a run scored against an unusual window — a
maintenance freeze, a capture gap, a fleet that has gone quiet — would otherwise
drag the threshold to wherever that window implies. The requested value is
clamped, not rejected: refusing to move at all would freeze the threshold the
first time the data is odd, and clamping still lets a genuine drift accumulate
over several runs.

**Every change is written to the audit log, including the clamped ones.** The
most interesting entry in the log is not the change that was applied but the one
that was asked for and refused, because that is a record of the data disagreeing
with the model.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Final

#: Largest movement one calibration run may apply (T-207).
DEFAULT_GUARDRAIL: Final = 0.10

#: Quantile of benign scores an alert threshold is fitted at, giving a target
#: false-positive rate of 1%.
DEFAULT_QUANTILE: Final = 0.99


@dataclass(frozen=True, slots=True)
class ThresholdChange:
    """One calibration decision, in the form it is written to the audit log.

    Attributes:
        key: the family or tenant this threshold governs.
        previous: the threshold in force before this run.
        requested: what this run's fit asked for, *before* clamping.
        applied: what was actually applied, after clamping.
        clamped: whether the guardrail limited the movement. This is the field
            worth alerting on: a run that keeps hitting the guardrail means the
            fit and the deployed threshold disagree persistently.
        quantile: the quantile the threshold was fitted at.
        sample_size: how many benign scores the fit saw.
    """

    key: str
    previous: float
    requested: float
    applied: float
    clamped: bool
    quantile: float
    sample_size: int

    def movement(self) -> float:
        """The signed distance the threshold actually moved."""
        return self.applied - self.previous

    def as_json(self) -> str:
        """One audit-log line. Sorted keys so identical changes hash identically."""
        return json.dumps(asdict(self), sort_keys=True)


def quantile(values: Sequence[float], q: float) -> float:
    """The ``q``-th quantile by linear interpolation between order statistics.

    Implemented here rather than borrowed so the interpolation rule is fixed and
    visible: two libraries disagreeing on quantile convention would produce two
    different thresholds from one score distribution, and neither would be wrong.
    """
    if not 0.0 <= q <= 1.0:
        raise ValueError(f"q must be in [0, 1], got {q}")
    if not values:
        raise ValueError("cannot take a quantile of an empty sequence")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = q * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def fit_threshold(benign_scores: Sequence[float], *, quantile_: float = DEFAULT_QUANTILE) -> float:
    """Fit an alert threshold on benign traffic only.

    Fitting on all traffic would place the threshold inside the attack
    distribution and silently trade recall for a lower alert count.

    Raises:
        ValueError: if there are no benign scores, or if any score is out of range.
    """
    if not benign_scores:
        raise ValueError(
            "cannot fit a threshold without benign scores; fitting on attacks "
            "would place the threshold inside the attack distribution"
        )
    for score in benign_scores:
        if not 0.0 <= score <= 1.0:
            raise ValueError(f"score {score} outside [0, 1]")
    return quantile(benign_scores, quantile_)


def calibrate(
    key: str,
    requested: float,
    *,
    previous: float,
    guardrail: float = DEFAULT_GUARDRAIL,
    quantile_: float = DEFAULT_QUANTILE,
    sample_size: int = 0,
) -> ThresholdChange:
    """Clamp a requested threshold to within ``guardrail`` of the current one.

    The move is limited, not refused. Refusing would freeze the threshold the
    first time the calibration data is unusual, and a threshold that cannot move
    is not calibrated — it is abandoned.
    """
    if not 0.0 <= guardrail < 1.0:
        raise ValueError(f"guardrail must be in [0, 1), got {guardrail}")
    for name, value in (("requested", requested), ("previous", previous)):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be in [0, 1], got {value}")

    lower, upper = previous - guardrail, previous + guardrail
    applied = min(max(requested, lower), upper)
    # Snap back into range: near the ends of the interval the guardrail band
    # reaches past 0 or 1, and a threshold outside [0, 1] is meaningless.
    applied = min(max(applied, 0.0), 1.0)
    return ThresholdChange(
        key=key,
        previous=previous,
        requested=requested,
        applied=applied,
        clamped=abs(applied - requested) > 1e-12,
        quantile=quantile_,
        sample_size=sample_size,
    )


def append_audit(path: str, change: ThresholdChange) -> None:
    """Write one change to the audit log, creating the file if needed.

    Append-only and one JSON object per line, so the log can be read by anything
    and cannot be rewritten in place without that being visible.
    """
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(change.as_json())
        handle.write("\n")


def read_audit(path: str) -> list[ThresholdChange]:
    """Read the audit log back. A round trip must be lossless."""
    if not os.path.isfile(path):
        return []
    entries: list[ThresholdChange] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                entries.append(ThresholdChange(**json.loads(line)))
    return entries


def calibrate_and_record(
    path: str,
    key: str,
    benign_scores: Sequence[float],
    *,
    previous: float,
    guardrail: float = DEFAULT_GUARDRAIL,
    quantile_: float = DEFAULT_QUANTILE,
) -> ThresholdChange:
    """Fit, clamp and record in one call.

    This is the entry point production callers should use. Fitting and recording
    are separate functions, and separate functions get called separately — which
    is how a threshold ends up changed with no trace of it. Combining them makes
    the unrecorded change the thing that takes extra effort.
    """
    requested = fit_threshold(benign_scores, quantile_=quantile_)
    change = calibrate(
        key,
        requested,
        previous=previous,
        guardrail=guardrail,
        quantile_=quantile_,
        sample_size=len(benign_scores),
    )
    append_audit(path, change)
    return change
