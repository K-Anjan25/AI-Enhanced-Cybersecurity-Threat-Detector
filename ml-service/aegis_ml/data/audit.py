"""Leakage audit (T-111).

Four ways an evaluation can lie, each with a check here:

* **time leakage** — the model was tuned on the period it is scored on;
* **entity leakage** — the model memorised a host and was rewarded for it;
* **record leakage** — the same window reached two folds, which happens when
  windows overlap and the split is made on records rather than windows;
* **scaler leakage** — normalisation statistics saw data outside the training
  fold, which quietly transfers distribution information into every feature;
* **label leakage** — a derived feature encodes the label, so a model looks
  excellent and detects nothing.

Every check returns findings rather than raising, so a run can report all of
them at once. :meth:`AuditReport.raise_for_leaks` is the gate CI calls.

The audit deliberately does not trust :class:`~aegis_ml.data.splits.Split` to
have been built by :func:`~aegis_ml.data.splits.split_windows`. A hand-built or
hand-edited split must fail the same way, which is the only reason an audit is
worth having.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from aegis_ml.data.features import NUMERIC_FEATURES, FlowFeatures
from aegis_ml.data.records import FlowRecord, LogRecord
from aegis_ml.data.splits import Split
from aegis_ml.data.windowing import Window


class LeakKind(StrEnum):
    """The class of leakage a finding belongs to."""

    TIME = "time"
    ENTITY = "entity"
    RECORD = "record"
    SCALER = "scaler"
    LABEL = "label"


@dataclass(frozen=True, slots=True)
class Finding:
    """One detected leak. ``value`` carries the offending measurement if any."""

    kind: LeakKind
    detail: str
    value: float | None = None

    def __str__(self) -> str:
        """Render as ``kind: detail`` for logs and assertion messages."""
        return f"{self.kind.value}: {self.detail}"


@dataclass(frozen=True, slots=True)
class AuditReport:
    """Everything the audit found. Empty means clean."""

    findings: tuple[Finding, ...]

    @property
    def ok(self) -> bool:
        """Whether no leakage was found."""
        return not self.findings

    def kinds(self) -> frozenset[LeakKind]:
        """The distinct kinds of leakage found."""
        return frozenset(finding.kind for finding in self.findings)

    def raise_for_leaks(self) -> None:
        """Raise if anything was found. This is the CI gate.

        Raises:
            ValueError: naming every finding, so one run surfaces all of them
                instead of the first.
        """
        if self.findings:
            listed = "; ".join(str(finding) for finding in self.findings)
            raise ValueError(f"leakage audit failed — {listed}")


def window_id(window: Window[FlowRecord] | Window[LogRecord]) -> tuple[str, datetime]:
    """Return a stable identity for a window.

    Keyed on entity and start time rather than on the records themselves, so the
    audit works on windows rebuilt from the same stream and does not depend on
    record hashing.
    """
    return (window.key, window.start)


def check_time_leakage(split: Split[FlowRecord] | Split[LogRecord]) -> tuple[Finding, ...]:
    """Verify the folds are strictly ordered in time (R-60)."""
    findings: list[Finding] = []
    if not split.train or not split.test:
        return (Finding(LeakKind.TIME, "a fold is empty, so ordering cannot be verified"),)

    latest_train = max(window.start for window in split.train)
    earliest_valid = min(window.start for window in split.valid) if split.valid else None
    if earliest_valid is not None and earliest_valid <= latest_train:
        findings.append(
            Finding(
                LeakKind.TIME,
                f"validation starts at {earliest_valid.isoformat()}, no later than the "
                f"last training window at {latest_train.isoformat()}",
            )
        )
    if split.min_test_start <= split.max_train_start:
        findings.append(
            Finding(
                LeakKind.TIME,
                f"test starts at {split.min_test_start.isoformat()}, no later than the "
                f"last train/validation window at {split.max_train_start.isoformat()}",
            )
        )
    return tuple(findings)


def check_entity_leakage(split: Split[FlowRecord] | Split[LogRecord]) -> tuple[Finding, ...]:
    """Verify no entity appears in two folds (R-61)."""
    findings: list[Finding] = []
    pairs = (
        ("train", "valid", split.train_entities & split.valid_entities),
        ("train", "test", split.train_entities & split.test_entities),
        ("valid", "test", split.valid_entities & split.test_entities),
    )
    for left, right, shared in pairs:
        if shared:
            findings.append(
                Finding(
                    LeakKind.ENTITY,
                    f"{len(shared)} entit{'y' if len(shared) == 1 else 'ies'} appear in both "
                    f"{left} and {right}: {', '.join(sorted(shared)[:5])}",
                )
            )
    return tuple(findings)


def check_record_leakage(split: Split[FlowRecord] | Split[LogRecord]) -> tuple[Finding, ...]:
    """Verify no window reached two folds.

    Catches the failure mode where overlapping windows are split by record
    instead of by window, so adjacent windows share events across the boundary.
    """
    train = {window_id(window) for window in split.train}
    valid = {window_id(window) for window in split.valid}
    test = {window_id(window) for window in split.test}
    findings: list[Finding] = []
    for left, right, shared in (
        ("train", "valid", train & valid),
        ("train", "test", train & test),
        ("valid", "test", valid & test),
    ):
        if shared:
            findings.append(
                Finding(
                    LeakKind.RECORD,
                    f"{len(shared)} window(s) appear in both {left} and {right}",
                )
            )
    return tuple(findings)


def check_scaler_leakage(
    fit_on: Sequence[Window[FlowRecord]] | Sequence[Window[LogRecord]],
    split: Split[FlowRecord] | Split[LogRecord],
) -> tuple[Finding, ...]:
    """Verify normalisation statistics were fit on the training fold only (R-62).

    This is the check the task singles out: a scaler fit on train plus
    validation, or on the whole stream, must be caught.
    """
    train = {window_id(window) for window in split.train}
    outside = [window for window in fit_on if window_id(window) not in train]
    if not outside:
        return ()
    return (
        Finding(
            LeakKind.SCALER,
            f"scaler was fit on {len(outside)} window(s) outside the training fold",
            value=float(len(outside)),
        ),
    )


def check_label_leakage(rows: Sequence[FlowFeatures]) -> tuple[Finding, ...]:
    """Flag any single numeric feature that perfectly separates the labels.

    A feature whose sorted values group the labels into contiguous blocks means
    one threshold reproduces the label exactly. Real detection features are
    noisy; a perfectly separating one is almost always the label in disguise —
    for instance a derived feature computed from the label rather than the
    traffic.
    """
    labels = [row.label for row in rows]
    present = {label for label in labels if label is not None}
    if len(present) < 2:
        return ()

    pairs = [(row, label) for row, label in zip(rows, labels, strict=True) if label is not None]
    findings: list[Finding] = []
    for name in NUMERIC_FEATURES:
        ordered = sorted(pairs, key=lambda pair: pair[0].numeric_value(name))
        if _is_contiguous([label for _, label in ordered]):
            findings.append(
                Finding(
                    LeakKind.LABEL,
                    f"feature {name!r} perfectly separates the labels — a single "
                    "threshold reproduces the label exactly",
                )
            )
    return tuple(findings)


def _is_contiguous(labels: Sequence[str]) -> bool:
    """Return whether each distinct label occupies one unbroken run."""
    seen: set[str] = set()
    previous: str | None = None
    for label in labels:
        if label != previous:
            if label in seen:
                return False
            seen.add(label)
            previous = label
    return True


def audit_split(
    split: Split[FlowRecord] | Split[LogRecord],
    *,
    fit_on: Sequence[Window[FlowRecord]] | Sequence[Window[LogRecord]] | None = None,
    rows: Sequence[FlowFeatures] | None = None,
) -> AuditReport:
    """Run every applicable check and collect the findings.

    ``fit_on`` and ``rows`` are optional: the scaler check needs to know what the
    normalisation was fit on, and the label check needs extracted feature rows.
    Omitting either skips that check rather than passing it silently.
    """
    findings: list[Finding] = [
        *check_time_leakage(split),
        *check_entity_leakage(split),
        *check_record_leakage(split),
    ]
    if fit_on is not None:
        findings.extend(check_scaler_leakage(fit_on, split))
    if rows is not None:
        findings.extend(check_label_leakage(rows))
    return AuditReport(findings=tuple(findings))
