"""Temporal, entity-disjoint splitting (T-109).

Random splits on intrusion-detection data routinely inflate scores through
leakage (D-009), so this module enforces two invariants at once:

* **no time leakage** — every test window starts strictly after every train
  window, so the model can never be tuned on the period it is scored on;
* **no entity leakage** — no source or destination appears in two folds, so the
  model cannot memorise a host and be rewarded for it.

The two invariants conflict
---------------------------
An entity that is active on both sides of the time cut cannot be kept whole in
either fold without breaking one of the rules. Rather than quietly choosing, the
split **drops** the offending windows and reports how many. A smaller honest
split beats a larger leaky one; the dropped count is surfaced so the cost is
visible instead of silent (R-06).

Order of operations
-------------------
The test cut is made first, then the validation cut is made *within* what
remains. That keeps validation disjoint from both train and test, and keeps
test strictly later than validation.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Generic, TypeVar

from aegis_ml.data.records import FlowRecord, LogRecord
from aegis_ml.data.windowing import Window

#: Share of the timeline held back for test.
DEFAULT_TEST_FRACTION = 0.20

#: Share of the *remaining* timeline held back for validation.
DEFAULT_VALID_FRACTION = 0.15

R = TypeVar("R", FlowRecord, LogRecord)


@dataclass(frozen=True)
class Split(Generic[R]):
    """The three folds plus the numbers needed to audit them.

    ``dropped`` counts windows excluded to keep both invariants; it is not an
    error, but a split that drops most of the data is a warning sign worth
    reading before trusting any metric produced from it.
    """

    train: tuple[Window[R], ...]
    valid: tuple[Window[R], ...]
    test: tuple[Window[R], ...]
    test_cutoff: datetime
    valid_cutoff: datetime
    dropped: int

    @property
    def train_entities(self) -> frozenset[str]:
        """Entities represented in the training fold."""
        return frozenset(window.key for window in self.train)

    @property
    def valid_entities(self) -> frozenset[str]:
        """Entities represented in the validation fold."""
        return frozenset(window.key for window in self.valid)

    @property
    def test_entities(self) -> frozenset[str]:
        """Entities represented in the test fold."""
        return frozenset(window.key for window in self.test)

    def audit(self) -> dict[str, object]:
        """Return the invariants and their status, for logging and tests."""
        return {
            "train": len(self.train),
            "valid": len(self.valid),
            "test": len(self.test),
            "dropped": self.dropped,
            "train_entities": len(self.train_entities),
            "test_entities": len(self.test_entities),
            "test_after_train": self.min_test_start > self.max_train_start,
            "entities_disjoint": not (
                (self.train_entities & self.test_entities)
                or (self.train_entities & self.valid_entities)
                or (self.valid_entities & self.test_entities)
            ),
        }

    @property
    def max_train_start(self) -> datetime:
        """Latest window start in train and validation combined."""
        return max(window.start for window in (*self.train, *self.valid))

    @property
    def min_test_start(self) -> datetime:
        """Earliest window start in test."""
        return min(window.start for window in self.test)


def split_windows(
    windows: Sequence[Window[R]],
    *,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    valid_fraction: float = DEFAULT_VALID_FRACTION,
) -> Split[R]:
    """Split windows into train / valid / test under both leakage invariants.

    Raises:
        ValueError: if the input is empty, the fractions are unusable, or the
            data is too thin to produce three non-empty folds. Failing here is
            better than returning an empty fold that a caller would score as
            zero (R-06).
    """
    if not windows:
        raise ValueError("cannot split an empty sequence of windows")
    for name, value in (("test_fraction", test_fraction), ("valid_fraction", valid_fraction)):
        if not 0.0 < value < 1.0:
            raise ValueError(f"{name} must be in (0, 1), got {value}")
    if test_fraction + valid_fraction >= 1.0:
        raise ValueError("test_fraction and valid_fraction must leave room for training")

    trainvalid, test, dropped_test, test_cutoff = _cut(list(windows), test_fraction)
    train, valid, dropped_valid, valid_cutoff = _cut(trainvalid, valid_fraction)

    if not train or not valid or not test:
        raise ValueError(
            f"split produced empty folds (train={len(train)}, valid={len(valid)}, "
            f"test={len(test)}); the stream is too short or too concentrated in "
            "one entity for the requested fractions"
        )

    return Split(
        train=tuple(train),
        valid=tuple(valid),
        test=tuple(test),
        test_cutoff=test_cutoff,
        valid_cutoff=valid_cutoff,
        dropped=dropped_test + dropped_valid,
    )


def _cut(
    windows: list[Window[R]], fraction: float
) -> tuple[list[Window[R]], list[Window[R]], int, datetime]:
    """Make one temporal, entity-disjoint cut.

    Returns the early fold, the late fold, the number of dropped windows and the
    cutoff timestamp. Windows whose entity appears on both sides stay in the
    early fold and their late windows are dropped, which is what keeps the two
    folds entity-disjoint without moving anything backwards in time.
    """
    starts = sorted(window.start for window in windows)
    index = int(len(starts) * (1.0 - fraction))
    # Both sides must be non-empty for the cut to mean anything.
    index = min(max(index, 1), len(starts) - 1)
    cutoff = starts[index]

    early = [window for window in windows if window.start < cutoff]
    late_all = [window for window in windows if window.start >= cutoff]
    early_keys = {window.key for window in early}
    late = [window for window in late_all if window.key not in early_keys]
    dropped = len(late_all) - len(late)

    if not early or not late:
        raise ValueError(
            f"a cut at {cutoff.isoformat()} leaves one side empty "
            f"(early={len(early)}, late={len(late)}); every window may belong to "
            "a single entity or a single instant"
        )
    return early, late, dropped, cutoff
