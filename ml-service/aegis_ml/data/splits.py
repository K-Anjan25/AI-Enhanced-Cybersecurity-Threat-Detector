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

import hashlib
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

    ``entity_disjoint_enforced`` records whether R-61 was applied at all. When it
    is false the split is temporal only (R-60) and entities legitimately overlap
    across folds: that is the configuration published NIDS benchmarks are scored
    under, kept so results stay comparable, and never a release gate. The audit
    measures the overlap either way, so the cost of relaxing R-61 is reported
    rather than assumed.
    """

    train: tuple[Window[R], ...]
    valid: tuple[Window[R], ...]
    test: tuple[Window[R], ...]
    test_cutoff: datetime
    valid_cutoff: datetime
    dropped: int
    entity_disjoint_enforced: bool = True
    temporal_enforced: bool = True

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
            "entity_disjoint_enforced": self.entity_disjoint_enforced,
            "temporal_enforced": self.temporal_enforced,
            "train_entities": len(self.train_entities),
            "test_entities": len(self.test_entities),
            "test_after_train": self.min_test_start > self.max_train_start,
            # The size of the overlap, not just whether it is empty. Reporting a
            # count is what makes the cost of relaxing R-61 measurable instead of
            # asserted: two runs with the same entities_disjoint=False can differ
            # by an order of magnitude in how badly they leak.
            "shared_train_test_entities": len(self.train_entities & self.test_entities),
            "shared_train_valid_entities": len(self.train_entities & self.valid_entities),
            "shared_valid_test_entities": len(self.valid_entities & self.test_entities),
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
    entity_disjoint: bool = True,
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

    trainvalid, test, dropped_test, test_cutoff = _cut(
        list(windows), test_fraction, entity_disjoint=entity_disjoint
    )
    train, valid, dropped_valid, valid_cutoff = _cut(
        trainvalid, valid_fraction, entity_disjoint=entity_disjoint
    )

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
        entity_disjoint_enforced=entity_disjoint,
    )


def _cut(
    windows: list[Window[R]], fraction: float, *, entity_disjoint: bool
) -> tuple[list[Window[R]], list[Window[R]], int, datetime]:
    """Make one temporal, entity-disjoint cut.

    Returns the early fold, the late fold, the number of dropped windows and the
    cutoff timestamp. Windows whose entity appears on both sides stay in the
    early fold and their late windows are dropped, which is what keeps the two
    folds entity-disjoint without moving anything backwards in time (R-61).

    With ``entity_disjoint=False`` nothing is dropped and every window lands in
    the fold its start time implies. That leaks by construction - an entity seen
    in training reappears in test - so it is opt-in and the audit still counts
    the shared entities.
    """
    starts = sorted(window.start for window in windows)
    index = int(len(starts) * (1.0 - fraction))
    # Both sides must be non-empty for the cut to mean anything.
    index = min(max(index, 1), len(starts) - 1)
    cutoff = starts[index]

    early = [window for window in windows if window.start < cutoff]
    late_all = [window for window in windows if window.start >= cutoff]
    early_keys = {window.key for window in early}
    if entity_disjoint:
        late = [window for window in late_all if window.key not in early_keys]
    else:
        late = late_all
    dropped = len(late_all) - len(late)

    if not early or not late:
        raise ValueError(
            f"a cut at {cutoff.isoformat()} leaves one side empty "
            f"(early={len(early)}, late={len(late)}); every window may belong to "
            "a single entity or a single instant"
        )
    return early, late, dropped, cutoff


#: Number of hash buckets used to partition entities. Fine enough that the fold
#: sizes land close to the requested fractions, coarse enough that the arithmetic
#: stays readable.
ENTITY_BUCKETS = 10000


def _entity_bucket(key: str) -> int:
    """Return a stable bucket for an entity key, in ``[0, ENTITY_BUCKETS)``.

    SHA-256 rather than the builtin ``hash()``, which is salted per process and
    would reshuffle every fold on each run. Reproducibility is not optional here:
    a metric that moves when nothing else did cannot be compared to itself.
    """
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % ENTITY_BUCKETS


def group_split(
    windows: Sequence[Window[R]],
    *,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    valid_fraction: float = DEFAULT_VALID_FRACTION,
) -> Split[R]:
    """Partition whole entities into folds by a stable hash of their key (Q-07).

    This answers a different question from :func:`split_windows`. That one asks
    "does the model hold up on later traffic"; this one asks "does the model
    recognise an attack from an entity it has never seen". The second is the
    question a released detector actually has to answer, and it is the one no
    temporal split can ask on a capture whose attack sources are persistent.

    Entity disjointness is exact by construction: an entity lands in exactly one
    fold, so nothing is dropped and the overlap audit is zero by definition.

    Time order is deliberately ignored, so training may see traffic that
    postdates the test fold. That is the leak this policy accepts and the reason
    it is never the default. ``test_cutoff`` and ``valid_cutoff`` are set to the
    latest window start in the stream and must not be read as boundaries.

    Raises:
        ValueError: if the input is empty, the fractions are unusable, or a fold
            comes out empty — which happens when there are too few entities for
            the requested fractions to mean anything.
    """
    if not windows:
        raise ValueError("cannot split an empty sequence of windows")
    for name, value in (("test_fraction", test_fraction), ("valid_fraction", valid_fraction)):
        if not 0.0 < value < 1.0:
            raise ValueError(f"{name} must be in (0, 1), got {value}")
    if test_fraction + valid_fraction >= 1.0:
        raise ValueError("test_fraction and valid_fraction must leave room for training")

    test_cut = int(test_fraction * ENTITY_BUCKETS)
    valid_cut = int((test_fraction + valid_fraction) * ENTITY_BUCKETS)

    train: list[Window[R]] = []
    valid: list[Window[R]] = []
    test: list[Window[R]] = []
    for window in windows:
        bucket = _entity_bucket(window.key)
        if bucket < test_cut:
            test.append(window)
        elif bucket < valid_cut:
            valid.append(window)
        else:
            train.append(window)

    if not train or not valid or not test:
        raise ValueError(
            f"group split produced empty folds (train={len(train)}, valid={len(valid)}, "
            f"test={len(test)}); {len({w.key for w in windows})} distinct entities is too "
            "few for the requested fractions"
        )

    latest = max(window.start for window in windows)
    return Split(
        train=tuple(train),
        valid=tuple(valid),
        test=tuple(test),
        test_cutoff=latest,
        valid_cutoff=latest,
        dropped=0,
        entity_disjoint_enforced=True,
        temporal_enforced=False,
    )
